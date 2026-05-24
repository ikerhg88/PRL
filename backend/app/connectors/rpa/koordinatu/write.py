from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class KoordinatuWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="koordinatu",
        platform_key="koordinatu",
        connector_key="connector_rpa_koordinatu_write",
        display_name="Koordinatu",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
