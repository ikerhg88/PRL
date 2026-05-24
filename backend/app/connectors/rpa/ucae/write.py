from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class UcaeWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="ucae",
        platform_key="ucae",
        connector_key="connector_rpa_ucae_write",
        display_name="UCAE",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
