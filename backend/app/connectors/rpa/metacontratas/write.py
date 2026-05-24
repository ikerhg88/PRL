from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class MetacontratasWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="metacontratas",
        platform_key="metacontratas",
        connector_key="connector_rpa_metacontratas_write",
        display_name="Metacontratas",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
