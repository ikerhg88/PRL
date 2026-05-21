from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class TimenetWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="timenet",
        platform_key="timenet",
        connector_key="connector_rpa_timenet_write",
        display_name="Timenet",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
