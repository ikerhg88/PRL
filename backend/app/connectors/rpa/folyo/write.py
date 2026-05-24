from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class FolyoWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="folyo",
        platform_key="folyo",
        connector_key="connector_rpa_folyo_write",
        display_name="Folyo",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
