from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class NomioWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="nomio",
        platform_key="nomio",
        connector_key="connector_rpa_nomio_write",
        display_name="Nomio",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
