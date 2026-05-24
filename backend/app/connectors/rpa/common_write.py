from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.connectors.base import ConnectorContext, ConnectorResult, CoordinationPlatformConnector


SUPPORTED_WRITE_OPERATIONS = (
    "sync_company_profile",
    "upsert_worker",
    "deactivate_worker",
    "upload_worker_document",
    "upload_company_document",
    "upload_machine_vehicle_document",
)


@dataclass(frozen=True)
class WritePlatformProfile:
    platform_slug: str
    platform_key: str
    connector_key: str
    display_name: str
    supported_operations: tuple[str, ...] = SUPPORTED_WRITE_OPERATIONS


@dataclass(frozen=True)
class WriteHelperSpec:
    helper_key: str
    platform_slug: str
    connector_key: str
    display_name: str
    status: str
    supported_operations: tuple[str, ...]
    module_path: str | None = None
    script_path: str | None = None
    requires: tuple[str, ...] = (
        "platform_company_context_selected",
        "pre_write_duplicate_readback",
        "field_mapping_approved",
        "editable_screen_capture_approved",
        "preview_generated",
        "human_approval_recorded",
        "before_after_audit_enabled",
        "post_write_readback_confirmation",
    )
    commercial_routes_or_selectors_invented: bool = False
    captcha_bypass: bool = False
    mfa_bypass: bool = False

    @property
    def live_adapter_available(self) -> bool:
        return self.status == "live_implemented"

    def as_dict(self) -> dict[str, Any]:
        return {
            "helper_key": self.helper_key,
            "platform_slug": self.platform_slug,
            "connector_key": self.connector_key,
            "display_name": self.display_name,
            "status": self.status,
            "live_adapter_available": self.live_adapter_available,
            "supported_operations": list(self.supported_operations),
            "module_path": self.module_path,
            "script_path": self.script_path,
            "requires": list(self.requires),
            "commercial_routes_or_selectors_invented": self.commercial_routes_or_selectors_invented,
            "captcha_bypass": self.captcha_bypass,
            "mfa_bypass": self.mfa_bypass,
        }


class ConfiguredWriteConnector(CoordinationPlatformConnector):
    profile: WritePlatformProfile
    connector_type = "authorized_rpa_write"
    supports_dry_run = True
    manual_approval_required = True
    live_helper_status = "scaffolded_pending_capture"
    live_helper_module_path: str | None = None
    live_helper_script_path: str | None = None

    async def test_connection(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="preview_available",
            message=(
                f"{self.display_name}: conector de escritura registrado. "
                "La ejecucion externa requiere preview, mapeos aprobados y autorizacion."
            ),
            external_status="not_synced",
            evidence=self._base_evidence(context, operation="test_connection"),
        )

    async def sync_catalog(self, context: ConnectorContext) -> ConnectorResult:
        return ConnectorResult(
            status="mapping_review_required",
            message=(
                f"{self.display_name}: catalogo de escritura preparado; "
                "faltan mapeos completos aprobados por operacion antes de guardar fuera."
            ),
            external_status="not_synced",
            evidence=self._base_evidence(context, operation="sync_catalog"),
        )

    def helper_spec(self) -> WriteHelperSpec:
        return WriteHelperSpec(
            helper_key=f"{self.profile.platform_slug}_live_write_helper",
            platform_slug=self.profile.platform_slug,
            connector_key=self.connector_key,
            display_name=self.display_name,
            status=self.live_helper_status,
            supported_operations=self.profile.supported_operations,
            module_path=self.live_helper_module_path or f"app.connectors.rpa.{self.profile.platform_slug}.write",
            script_path=self.live_helper_script_path,
        )

    async def upload_document(
        self,
        context: ConnectorContext,
        document_metadata: dict[str, Any],
    ) -> ConnectorResult:
        operation = str(document_metadata.get("operation") or "upload_worker_document")
        prepared_fields = [
            field
            for field in ("document_code", "filename", "sha256")
            if document_metadata.get(field) is not None
        ]
        metadata = {
            "document_code": document_metadata.get("document_code"),
            "filename": document_metadata.get("filename"),
            "sha256_present": bool(document_metadata.get("sha256")),
        }
        if not context.dry_run:
            return self._blocked_live_adapter_missing_result(
                context,
                operation=operation,
                prepared_fields=prepared_fields,
                metadata=metadata,
            )
        return self._blocked_until_mapping_result(
            context,
            operation=operation,
            prepared_fields=prepared_fields,
            metadata=metadata,
        )

    async def upsert_worker(
        self,
        context: ConnectorContext,
        worker_metadata: dict[str, Any],
    ) -> ConnectorResult:
        prepared_fields = list(worker_metadata.get("prepared_fields") or [])
        metadata = {
            "worker_ref": worker_metadata.get("worker_ref"),
            "prepared_fields": worker_metadata.get("prepared_fields", []),
        }
        if not context.dry_run:
            return self._blocked_live_adapter_missing_result(
                context,
                operation="upsert_worker",
                prepared_fields=prepared_fields,
                metadata=metadata,
            )
        return self._blocked_until_mapping_result(
            context,
            operation="upsert_worker",
            prepared_fields=prepared_fields,
            metadata=metadata,
        )

    def _blocked_until_mapping_result(
        self,
        context: ConnectorContext,
        *,
        operation: str,
        prepared_fields: list[str],
        metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="blocked_mapping_review_required",
            message=(
                f"{self.display_name}: operacion {operation} preparada en dry-run, "
                "pero no se escribe en la plataforma hasta completar mapeo aprobado de todos los campos."
            ),
            external_status="not_synced",
            evidence=self._base_evidence(context, operation=operation)
            | {
                "external_write_executed": False,
                "persist_external_status": False,
                "prepared_fields": prepared_fields,
                "metadata": metadata,
                "required_before_live_write": [
                    "platform_company_context_selected",
                    "field_mapping_approved",
                    "editable_screen_capture_approved",
                    "preview_generated",
                    "human_approval_recorded",
                    "before_after_audit_enabled",
                ],
            },
        )

    def _blocked_live_adapter_missing_result(
        self,
        context: ConnectorContext,
        *,
        operation: str,
        prepared_fields: list[str],
        metadata: dict[str, Any],
    ) -> ConnectorResult:
        return ConnectorResult(
            status="blocked_live_adapter_missing",
            message=(
                f"{self.display_name}: operacion live {operation} bloqueada. "
                "Falta helper especifico de plataforma con lectura previa, submit autorizado y lectura posterior."
            ),
            external_status="not_synced",
            evidence=self._base_evidence(context, operation=operation)
            | {
                "external_write_executed": False,
                "post_write_read_confirmed": False,
                "valid_external_write": False,
                "persist_external_status": False,
                "helper": self.helper_spec().as_dict(),
                "prepared_fields": prepared_fields,
                "metadata": metadata,
                "required_before_live_write": [
                    "platform_specific_live_adapter",
                    "pre_write_duplicate_readback",
                    "field_mapping_approved",
                    "editable_screen_capture_approved",
                    "preview_generated",
                    "human_approval_recorded",
                    "post_write_readback_confirmation",
                    "before_after_audit_enabled",
                ],
            },
        )

    def _base_evidence(self, context: ConnectorContext, *, operation: str) -> dict[str, Any]:
        return {
            "connector_key": self.connector_key,
            "platform_slug": self.profile.platform_slug,
            "platform_key": context.platform_key,
            "operation": operation,
            "dry_run": context.dry_run,
            "manual_approval_required": context.manual_approval_required,
            "captcha_bypass": False,
            "stores_credentials_or_tokens": False,
            "supported_operations": list(self.profile.supported_operations),
            "helper": self.helper_spec().as_dict(),
        }
