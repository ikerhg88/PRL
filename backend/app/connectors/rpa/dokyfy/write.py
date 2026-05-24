from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class DokyfyWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="dokyfy",
        platform_key="dokify",
        connector_key="connector_rpa_dokyfy_write",
        display_name="Dokyfy",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
