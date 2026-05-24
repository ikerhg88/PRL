from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class EGestionaWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="egestiona",
        platform_key="egestiona",
        connector_key="connector_rpa_egestiona_write",
        display_name="eGestiona / Subcontratas",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
