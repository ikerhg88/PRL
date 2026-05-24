from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class QuiooWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="quioo",
        platform_key="quioo",
        connector_key="connector_rpa_quioo_write",
        display_name="Quioo / QUIO",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
