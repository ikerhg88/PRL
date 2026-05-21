from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class VitalyCaeWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="vitaly_cae",
        platform_key="vitaly_cae",
        connector_key="connector_rpa_vitaly_cae_write",
        display_name="Vitaly CAE",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
