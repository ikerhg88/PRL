from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorContext, ConnectorResult, CoordinationPlatformConnector


class ManualExportConnector(CoordinationPlatformConnector):
    connector_key = "connector_manual_export"
    display_name = "Exportacion manual asistida"
    connector_type = "manual_export"
    supports_dry_run = True
    manual_approval_required = True

    async def test_connection(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="Exportacion manual disponible; no conecta con sistemas externos.",
            external_status="manual_required",
            evidence={"platform_key": context.platform_key},
        )

    async def sync_catalog(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="La exportacion manual usa el catalogo interno y mapeos revisados.",
            external_status="manual_required",
            evidence={"dry_run": context.dry_run},
        )

    async def upload_document(
        self,
        context: ConnectorContext,
        document_metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="manual_followup_required",
            message="Preparado plan de exportacion manual; no se ha escrito en plataforma externa.",
            external_status="manual_required",
            evidence={
                "target_platform": context.platform_key,
                "document_code": document_metadata.get("document_code"),
                "filename": document_metadata.get("filename"),
                "sha256": document_metadata.get("sha256"),
                "manual_approval_required": True,
            },
        )

    async def upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="manual_followup_required",
            message="Preparado plan de alta manual de trabajador; no se ha escrito en plataforma externa.",
            external_status="manual_required",
            evidence={
                "operation": "upsert_worker",
                "target_platform": context.platform_key,
                "worker_ref": worker_metadata.get("worker_ref"),
                "prepared_fields": worker_metadata.get("prepared_fields", []),
                "manual_approval_required": True,
            },
        )
