from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class ECoordinaWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="e_coordina",
        platform_key="ecoordina",
        connector_key="connector_rpa_e_coordina_write",
        display_name="e-coordina",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
