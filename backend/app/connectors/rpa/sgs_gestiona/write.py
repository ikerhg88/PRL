from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class SgsGestionaWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="sgs_gestiona",
        platform_key="sgs_gestiona",
        connector_key="connector_rpa_sgs_gestiona_write",
        display_name="SGS Gestiona",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
