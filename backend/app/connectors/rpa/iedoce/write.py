from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class IEDOCEWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="iedoce",
        platform_key="iedoce",
        connector_key="connector_rpa_iedoce_write",
        display_name="IEDOCE",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
