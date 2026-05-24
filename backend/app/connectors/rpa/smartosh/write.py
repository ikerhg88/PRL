from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class SmartoshWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="smartosh",
        platform_key="smartosh",
        connector_key="connector_rpa_smartosh_write",
        display_name="SmartOSH",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
