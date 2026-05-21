from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorContext, ConnectorResult, CoordinationPlatformConnector


class DemoConnector(CoordinationPlatformConnector):
    connector_key = "connector_demo"
    display_name = "Conector demo local"
    connector_type = "demo"
    supports_dry_run = True
    manual_approval_required = True

    async def test_connection(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="Conector demo disponible sin plataforma externa real.",
            external_status="not_synced",
            evidence={"platform_key": context.platform_key, "dry_run": context.dry_run},
        )

    async def sync_catalog(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="Catalogo demo sincronizado en memoria.",
            external_status="accepted",
            evidence={"catalog_items": 3, "dry_run": context.dry_run},
        )

    async def upload_document(
        self,
        context: ConnectorContext,
        document_metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="Documento aceptado por el simulador demo.",
            external_status="accepted",
            evidence={
                "document_code": document_metadata.get("document_code"),
                "sha256": document_metadata.get("sha256"),
                "dry_run": context.dry_run,
                "manual_approval_required": context.manual_approval_required,
            },
        )

    async def upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="ok",
            message="Trabajador aceptado por el simulador demo; no se ha escrito en terceros.",
            external_status="accepted",
            evidence={
                "operation": "upsert_worker",
                "worker_ref": worker_metadata.get("worker_ref"),
                "prepared_fields": worker_metadata.get("prepared_fields", []),
                "dry_run": context.dry_run,
                "manual_approval_required": context.manual_approval_required,
            },
        )
