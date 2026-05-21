from __future__ import annotations

from fastapi import APIRouter

from app.connectors.base import ConnectorContext
from app.connectors.registry import get_connector
from app.platforms.catalog import default_platform_catalog
from app.schemas import SystemPlatformModuleRead

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/platform-modules", response_model=list[SystemPlatformModuleRead])
async def list_system_platform_modules() -> list[SystemPlatformModuleRead]:
    modules: list[SystemPlatformModuleRead] = []
    for platform in default_platform_catalog():
        for method in platform.methods:
            health_status = "disabled"
            health_message = "Modulo no implementado; requiere documentacion/autorizacion antes de activarse."
            if method.implemented and method.connector_key is not None:
                connector = get_connector(method.connector_key)
                result = await connector.test_connection(
                    ConnectorContext(
                        tenant_id="system",
                        platform_key=platform.platform_key,
                        dry_run=True,
                        manual_approval_required=True,
                    )
                )
                health_status = result.status
                health_message = result.message
            modules.append(
                SystemPlatformModuleRead(
                    platform_key=platform.platform_key,
                    platform_name=platform.name,
                    method_key=method.method_key,
                    connector_type=method.connector_type,
                    connector_key=method.connector_key,
                    implemented=method.implemented,
                    status=method.status,
                    health_status=health_status,
                    health_message=health_message,
                    dry_run_supported=method.dry_run_supported,
                    manual_approval_required=method.manual_approval_required,
                    tenant_config_required=method.implemented,
                    notes=method.notes,
                )
            )
    return modules
