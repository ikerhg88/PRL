from __future__ import annotations

from app.connectors.rpa.common_write import ConfiguredWriteConnector, WritePlatformProfile


class IntegraAsemWriteConnector(ConfiguredWriteConnector):
    profile = WritePlatformProfile(
        platform_slug="integra_asem",
        platform_key="asemwebservices_integra",
        connector_key="connector_rpa_integra_asem_write",
        display_name="Integra ASEM Webservices",
    )
    connector_key = profile.connector_key
    display_name = profile.display_name
    platform_slug = profile.platform_slug
