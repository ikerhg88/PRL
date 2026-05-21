from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class CtaimaWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="ctaima",
        platform_key="ctaima_cae",
        connector_key="connector_rpa_ctaima_write",
        display_name="CTAIMA / CTAIMA CAE",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
