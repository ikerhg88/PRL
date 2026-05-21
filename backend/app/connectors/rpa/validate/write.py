from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class ValidateWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="validate",
        platform_key="validate",
        connector_key="connector_rpa_validate_write",
        display_name="Validate",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
